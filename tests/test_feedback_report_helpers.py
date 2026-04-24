import json
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from scripts.generate_feedback_report import _build_root_cause_summary, _collect_negative_samples


class FeedbackReportHelpersTests(unittest.TestCase):
    def test_build_root_cause_summary_uses_columns_and_metadata(self) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            SimpleNamespace(
                feedback_value="down",
                root_cause="missing_evidence",
                metadata_json=json.dumps({"root_cause": "wrong_jurisdiction"}),
                created_at=now,
            ),
            SimpleNamespace(
                feedback_value="down",
                root_cause=None,
                metadata_json=json.dumps({"root_cause": "wrong_jurisdiction"}),
                created_at=now,
            ),
            SimpleNamespace(
                feedback_value="down",
                root_cause=None,
                metadata_json=None,
                created_at=now,
            ),
        ]

        summary = _build_root_cause_summary(rows)
        counts = {item.root_cause: item.count for item in summary}

        self.assertEqual(counts.get("missing_evidence"), 1)
        self.assertEqual(counts.get("wrong_jurisdiction"), 1)
        self.assertEqual(counts.get("unspecified"), 1)

    def test_collect_negative_samples_carries_risk_fields(self) -> None:
        now = datetime.now(timezone.utc)
        rows = [
            SimpleNamespace(
                feedback_value="down",
                parsed_intent="ask_case",
                prompt_text="Prompt",
                response_text="Response",
                comment="Comment",
                created_at=now,
                metadata_json=json.dumps({
                    "ui_language": "en",
                    "root_cause": "ungrounded",
                    "jurisdiction": "germany",
                    "legal_domain": True,
                }),
                root_cause=None,
                jurisdiction=None,
                legal_domain=None,
            )
        ]

        samples = _collect_negative_samples(rows)
        self.assertIn("ask_case", samples)
        self.assertEqual(len(samples["ask_case"]), 1)
        sample = samples["ask_case"][0]
        self.assertEqual(sample.get("root_cause"), "ungrounded")
        self.assertEqual(sample.get("jurisdiction"), "germany")
        self.assertEqual(sample.get("legal_domain"), "true")


if __name__ == "__main__":
    unittest.main()
