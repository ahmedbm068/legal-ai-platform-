"""Week 1 DoD coverage — RFC 7807 problem+json error envelope contract."""
from __future__ import annotations

import json
import unittest

from backend.main import _problem


class ProblemJsonEnvelopeTests(unittest.TestCase):
    def _decode(self, response) -> dict:
        body = response.body
        if isinstance(body, (bytes, bytearray)):
            body = body.decode("utf-8")
        return json.loads(body)

    def test_problem_returns_rfc7807_media_type(self) -> None:
        response = _problem(404, "Not Found", "Case 99 was not found.", "/cases/99")
        self.assertEqual(response.media_type, "application/problem+json")
        self.assertEqual(response.status_code, 404)

    def test_problem_includes_all_mandatory_fields(self) -> None:
        response = _problem(403, "Forbidden", "Admin role required.", "/admin/users")
        payload = self._decode(response)
        for field in ("type", "title", "status", "detail", "instance"):
            self.assertIn(field, payload, f"missing field: {field}")
        self.assertEqual(payload["status"], 403)
        self.assertEqual(payload["title"], "Forbidden")
        self.assertEqual(payload["detail"], "Admin role required.")
        self.assertEqual(payload["instance"], "/admin/users")
        self.assertTrue(payload["type"].startswith("https://"))

    def test_problem_omits_instance_when_empty(self) -> None:
        response = _problem(500, "Internal Server Error", "Boom.", "")
        payload = self._decode(response)
        self.assertNotIn("instance", payload)

    def test_problem_status_matches_response_status(self) -> None:
        for code in (400, 401, 403, 404, 409, 422, 429, 500):
            response = _problem(code, f"err{code}", "detail", "/x")
            payload = self._decode(response)
            self.assertEqual(response.status_code, code)
            self.assertEqual(payload["status"], code)


if __name__ == "__main__":
    unittest.main()
