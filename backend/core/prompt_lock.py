"""
Prompt lock validator — verifies AI prompt files match their frozen SHA-256 hashes.

Called at application startup. On hash mismatch it logs a WARNING (does not crash
the server) so that a dev-time edit doesn't take down production, but the drift is
surfaced immediately in logs.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_LOCK_FILE = Path(__file__).parent.parent / "services" / "ai" / "agents" / "PROMPT_LOCK.json"
_AGENTS_DIR = Path(__file__).parent.parent / "services" / "ai" / "agents"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def validate_prompt_lock() -> bool:
    """
    Returns True if all locked prompts match their recorded hashes.
    Logs a WARNING for every mismatch and an INFO when all pass.
    """
    if not _LOCK_FILE.exists():
        logger.warning(
            "[PromptLock] PROMPT_LOCK.json not found at %s — "
            "failing validation. Run: python scripts/freeze_prompts.py",
            _LOCK_FILE,
        )
        return False

    try:
        lock = json.loads(_LOCK_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to parse PROMPT_LOCK.json: %s", exc)
        return False

    prompts: dict = lock.get("prompts", {})
    all_ok = True

    for filename, meta in prompts.items():
        target = _AGENTS_DIR / filename
        if not target.exists():
            logger.warning("[PromptLock] Prompt file missing: %s", filename)
            all_ok = False
            continue

        actual = _sha256(target)
        expected = (meta.get("sha256") or "").upper()

        if actual != expected:
            logger.warning(
                "[PromptLock] HASH MISMATCH for %s (version %s). "
                "Expected %s, got %s. "
                "If intentional, bump version and re-run: python scripts/freeze_prompts.py",
                filename,
                meta.get("version", "?"),
                expected,
                actual,
            )
            all_ok = False
        else:
            logger.debug("[PromptLock] %s v%s OK", filename, meta.get("version", "?"))

    if all_ok:
        logger.info("[PromptLock] All %d prompt(s) verified against lock file.", len(prompts))

    return all_ok
