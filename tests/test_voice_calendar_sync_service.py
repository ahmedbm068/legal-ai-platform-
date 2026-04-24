import unittest

from backend.services.voice_calendar_sync_service import VoiceCalendarSyncService


class VoiceCalendarSyncServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = VoiceCalendarSyncService()

    def test_extract_key_dates_includes_generic_absolute_mentions(self) -> None:
        text = "Let's review everything on 21st March, 2026 and finalize next actions."
        dates = self.service._extract_key_date_items(text)
        values = {item.get("value") for item in dates}

        self.assertIn("21 March 2026", values)

    def test_extract_key_dates_preserves_context_labeled_items(self) -> None:
        text = "The hearing is scheduled for 15 March 2026 before the commercial court."
        dates = self.service._extract_key_date_items(text)

        self.assertTrue(any(item.get("label") == "hearing_date" for item in dates))

    def test_parse_absolute_datetime(self) -> None:
        parsed = self.service._parse_absolute_datetime("2026-04-10")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 4)
        self.assertEqual(parsed.day, 10)


if __name__ == "__main__":
    unittest.main()
