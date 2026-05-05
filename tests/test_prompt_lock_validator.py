"""Week 1 DoD coverage — prompt lock validator fail-closed contract."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from backend.core import prompt_lock as pl


class PromptLockValidatorTests(unittest.TestCase):
    def test_missing_lock_file_returns_false(self) -> None:
        # Critical security property: if PROMPT_LOCK.json is missing, validation
        # MUST fail closed (return False) — never silently pass.
        with mock.patch.object(pl, "_LOCK_FILE", Path("/definitely/does/not/exist.json")):
            self.assertFalse(pl.validate_prompt_lock())

    def test_corrupt_lock_file_returns_false(self) -> None:
        with mock.patch.object(pl, "_LOCK_FILE", mock.MagicMock()) as fake:
            fake.exists.return_value = True
            fake.read_text.return_value = "{not valid json"
            self.assertFalse(pl.validate_prompt_lock())

    def test_real_repo_lock_file_validates(self) -> None:
        # The repo's own PROMPT_LOCK.json must validate against its checked-in
        # prompts at all times. If this fails on main, prompts have drifted.
        result = pl.validate_prompt_lock()
        self.assertTrue(
            result,
            "Repo PROMPT_LOCK.json drift detected — run scripts/freeze_prompts.py",
        )


if __name__ == "__main__":
    unittest.main()
