import unittest

from backend.services.document_calendar_sync_service import DocumentCalendarSyncService


class DocumentCalendarSyncServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = DocumentCalendarSyncService()

    def test_parse_absolute_date_text(self) -> None:
        parsed = self.service._parse_absolute_datetime("15 March 2026")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.year, 2026)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 15)
        self.assertEqual(parsed.hour, self.service.DEFAULT_EVENT_HOUR_UTC)

    def test_parse_relative_deadline_returns_none(self) -> None:
        parsed = self.service._parse_absolute_datetime("within 10 business days")
        self.assertIsNone(parsed)

    def test_normalize_date_text_removes_ordinal_suffixes(self) -> None:
        normalized = self.service._normalize_date_text("21st March, 2026")
        self.assertEqual(normalized, "21 March 2026")


if __name__ == "__main__":
    unittest.main()
