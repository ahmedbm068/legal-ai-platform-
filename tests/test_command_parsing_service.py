import unittest

from backend.services.ai.command_parsing_service import command_parsing_service


class CommandParsingServiceTests(unittest.TestCase):
    def test_case_update_with_field_assignments(self) -> None:
        parsed = command_parsing_service.parse(
            'case #42 set title to "Major Breach Escalation" and status to closed'
        )
        self.assertEqual(parsed["intent"], "update_case")
        self.assertEqual(parsed["case_id"], 42)

    def test_client_update_with_compound_fields(self) -> None:
        parsed = command_parsing_service.parse(
            "client #8 set phone to +21626002544 and email to legal@example.com"
        )
        self.assertEqual(parsed["intent"], "update_client")
        self.assertEqual(parsed["client_id"], 8)

    def test_prompt_library_update_complex_phrase(self) -> None:
        parsed = command_parsing_service.parse(
            "for prompt #3 set category to litigation and mark as favorite"
        )
        self.assertEqual(parsed["intent"], "update_prompt_library_entry")
        self.assertEqual(parsed["prompt_library_entry_id"], 3)

    def test_prompt_library_list_phrase(self) -> None:
        parsed = command_parsing_service.parse("show prompt library")
        self.assertEqual(parsed["intent"], "list_prompt_library")

    def test_appointment_update_with_date_and_location(self) -> None:
        parsed = command_parsing_service.parse(
            "appointment #7 set location to Teams and move to 2026-07-01 14:30"
        )
        self.assertEqual(parsed["intent"], "update_case_appointment")
        self.assertEqual(parsed["appointment_id"], 7)

    def test_parse_returns_confidence_score_and_low_confidence(self) -> None:
        parsed = command_parsing_service.parse("Hello")
        self.assertIn("confidence", parsed)
        self.assertIn("confidence_score", parsed)
        self.assertIn("low_confidence", parsed)
        self.assertIsInstance(parsed["confidence_score"], float)
        self.assertIsInstance(parsed["low_confidence"], bool)

    def test_parse_returns_arbitration_candidates(self) -> None:
        parsed = command_parsing_service.parse("Can you maybe review this?")
        self.assertIn("arbitration_candidates", parsed)
        self.assertIsInstance(parsed["arbitration_candidates"], list)
        self.assertGreaterEqual(len(parsed["arbitration_candidates"]), 1)


if __name__ == "__main__":
    unittest.main()
